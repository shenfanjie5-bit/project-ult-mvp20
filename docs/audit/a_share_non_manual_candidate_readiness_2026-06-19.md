# A-share non-manual candidate readiness

- Generated: `2026-06-19T19:47:44+08:00`
- Non-manual tasks: `28`
- Placeholder contracts valid: `28`
- Output contract shapes valid: `28`
- Bridge probes ready: `28`
- Deterministic Known drafts allowed: `0`
- Safe to upsert without review: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Route Bucket Counts

| Bucket | Count |
|---|---:|
| `event_text_classification_required` | 12 |
| `local_single_dependency_policy_required` | 3 |
| `local_structured_llm_required` | 10 |
| `local_structured_text_llm_required` | 3 |

## Rows

| dp_id | kind | target | route bucket | dependency readiness | bridge probe |
|---|---|---|---|---|---:|
| `L0.compete.new_entrant` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.compete.price_war` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.compete.share_concentration` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.cost.cac` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.cost.labor` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.cost.rent` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.demand.frequency` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.demand.penetration` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.demand.replacement` | `local_llm_candidate` | `fundamental_score` | `local_single_dependency_policy_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.demand.terminal` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.demand.user_count` | `local_llm_candidate` | `fundamental_score` | `local_structured_text_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.policy.access_license` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.policy.regulation` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.policy.subsidy` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.policy.tax_trade` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.price.contract_spot` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.price.discount` | `local_llm_candidate` | `fundamental_score` | `local_structured_text_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.price.pricing_power` | `local_llm_candidate` | `fundamental_score` | `local_single_dependency_policy_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.price.product_asp` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.supply.capacity` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.supply.chain_eff` | `local_llm_candidate` | `fundamental_score` | `local_structured_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.supply.channel_service` | `local_llm_candidate` | `fundamental_score` | `local_structured_text_llm_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.supply.inventory` | `local_llm_candidate` | `fundamental_score` | `local_single_dependency_policy_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.tech.ai_automation` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.tech.breakthrough` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L0.tech.substitute_tech` | `event_llm_candidate` | `fundamental_score` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L8.shock.black_swan` | `event_llm_candidate` | `risk_discount` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |
| `L8.shock.supply_break` | `event_llm_candidate` | `risk_discount` | `event_text_classification_required` | `all_dependencies_have_material_known_coverage` | yes |

## Interpretation

- This audit proves input readiness and bridge-contract reachability only.
- It deliberately emits 0 deterministic Known drafts because these local/event rows still need governed LLM or policy review to assign business direction and magnitude.
- Production score-affecting writes remain disabled.
