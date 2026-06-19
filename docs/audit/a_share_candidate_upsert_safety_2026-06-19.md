# A-share candidate upsert safety

- Generated: `2026-06-19T19:47:42+08:00`
- Candidate rows checked: `32`
- Candidate inputs ready: `32`
- Bridge ready: `32`
- Review-gated: `32`
- Blocked: `0`
- Safe to upsert without review: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Safety Class Counts

| Safety class | Count |
|---|---:|
| `review_required` | 32 |

## Rows

| dp_id | route | candidate status | bridge | safety class | action | reason |
|---|---|---|---:|---|---|---|
| `L0.compete.new_entrant` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.compete.price_war` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.compete.share_concentration` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.cost.cac` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.cost.labor` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.cost.rent` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.demand.frequency` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.demand.penetration` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.demand.replacement` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.demand.terminal` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.demand.user_count` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.policy.access_license` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.policy.regulation` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.policy.subsidy` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.policy.tax_trade` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.price.contract_spot` | `local_llm_closed_loop` | `ready_for_local_llm_candidate_with_grain_join` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.price.discount` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.price.pricing_power` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.price.product_asp` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.supply.capacity` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.supply.chain_eff` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.supply.channel_service` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.supply.inventory` | `local_llm_closed_loop` | `ready_for_local_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime dependencies exist, but local candidate inference output remains unreviewed |
| `L0.tech.ai_automation` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.tech.breakthrough` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L0.tech.substitute_tech` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L8.shock.black_swan` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L8.shock.supply_break` | `event_llm_from_runtime_news` | `ready_for_event_llm_candidate` | yes | `review_required` | `review_then_stage` | runtime event evidence exists, but event classification and value polarity remain unreviewed |
| `L6.mult.dcf` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | `review_required` | `review_then_stage` | manual-design candidate policy exists, but the generated value and assumptions remain unreviewed |
| `L6.priced.realization_risk` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | `review_required` | `review_then_stage` | manual-design candidate policy exists, but the generated value and assumptions remain unreviewed |
| `L7.reflex.tag` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | `review_required` | `review_then_stage` | manual-design candidate policy exists, but the generated value and assumptions remain unreviewed |
| `L8.val.slope_risk_off` | `manual_design_review` | `ready_for_manual_design_candidate` | yes | `review_required` | `review_then_stage` | manual-design candidate policy exists, but the generated value and assumptions remain unreviewed |

## Interpretation

- Bridge-ready rows prove the payload shape can reach scoring; they do not prove candidate values are correct.
- All non-blocked rows remain review-gated and staging-only until generated values, assumptions, and evidence refs are reviewed.
- `safe_to_upsert_without_review` must stay 0 for the current A-share candidate set.
