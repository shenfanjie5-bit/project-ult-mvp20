# A-share gap candidate evidence

- Generated: `2026-06-19T19:47:42+08:00`
- Blocking gaps packaged: `32`
- Candidate inputs ready: `32`
- Candidate inputs not ready: `0`
- Safe to upsert without review: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Candidate Status Counts

| Status | Count |
|---|---:|
| `ready_for_event_llm_candidate` | 12 |
| `ready_for_local_llm_candidate` | 15 |
| `ready_for_local_llm_candidate_with_grain_join` | 1 |
| `ready_for_manual_design_candidate` | 4 |

## Rows

| dp_id | route | status | ready | deps missing runtime rows | note |
|---|---|---|---:|---|---|
| `L0.compete.new_entrant` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.compete.price_war` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.compete.share_concentration` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.cost.cac` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.cost.labor` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.cost.rent` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.demand.frequency` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.demand.penetration` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.demand.replacement` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.demand.terminal` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.demand.user_count` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.policy.access_license` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.policy.regulation` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.policy.subsidy` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.policy.tax_trade` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.price.contract_spot` | `local_llm_closed_loop` | `ready_for_local_llm_candidate_with_grain_join` | yes | - | Runtime dependencies are present with an explicit stock-to-industry grain join policy; generate candidates only for mapped stocks (1007 A-share universe rows). |
| `L0.price.discount` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.price.pricing_power` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.price.product_asp` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.supply.capacity` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.supply.chain_eff` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.supply.channel_service` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.supply.inventory` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | - | Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference. |
| `L0.tech.ai_automation` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.tech.breakthrough` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L0.tech.substitute_tech` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L8.shock.black_swan` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L8.shock.supply_break` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | - | Runtime news/event dependencies are present and can be packaged for event classification. |
| `L6.mult.dcf` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | - | Formula/applicability policy is now explicit and runtime evidence can be packaged for governed candidate review; no runtime score write is allowed without separate validation. |
| `L6.priced.realization_risk` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | - | Formula/applicability policy is now explicit and runtime evidence can be packaged for governed candidate review; no runtime score write is allowed without separate validation. |
| `L7.reflex.tag` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | - | Formula/applicability policy is now explicit and runtime evidence can be packaged for governed candidate review; no runtime score write is allowed without separate validation. |
| `L8.val.slope_risk_off` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | - | Formula/applicability policy is now explicit and runtime evidence can be packaged for governed candidate review; no runtime score write is allowed without separate validation. |

## Interpretation

- Ready rows mean dependency evidence exists and can be sent through a local candidate-generation/review step.
- No not-ready rows remain in this candidate-input audit; runtime upserts still require separate value validation and review.
- This report does not change scores; it only narrows the next fill workload from generic gaps to evidence-backed candidate inputs.
