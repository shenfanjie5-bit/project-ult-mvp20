# A-share candidate score dry-run

- Generated: `2026-06-19T19:47:42+08:00`
- Score mutation: `none; dry-run only`
- Candidate-ready rows checked: `32`
- Bridge signal ready: `32`
- Realtime nodes emitted: `32`
- Final score target ready: `32`
- Bridge blocked: `0`

## Candidate Status Counts

| Status | Count |
|---|---:|
| `ready_for_event_llm_candidate` | 12 |
| `ready_for_local_llm_candidate` | 15 |
| `ready_for_local_llm_candidate_with_grain_join` | 1 |
| `ready_for_manual_design_candidate` | 4 |

## Rows

| dp_id | route | target | signal | node | payload |
|---|---|---|---:|---:|---|
| `L0.compete.new_entrant` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.compete.price_war` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.compete.share_concentration` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.cost.cac` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.cost.labor` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.cost.rent` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.demand.frequency` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.demand.penetration` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.demand.replacement` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.demand.terminal` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.demand.user_count` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.policy.access_license` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.policy.regulation` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.policy.subsidy` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.policy.tax_trade` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.price.contract_spot` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.price.discount` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.price.pricing_power` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.price.product_asp` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.supply.capacity` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.supply.chain_eff` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.supply.channel_service` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.supply.inventory` | `local_llm_closed_loop` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.tech.ai_automation` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.tech.breakthrough` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L0.tech.substitute_tech` | `event_llm_from_runtime_news` | `fundamental_score` | 0.1 | yes | `{"score": 0.1}` |
| `L8.shock.black_swan` | `event_llm_from_runtime_news` | `risk_discount` | 0.2 | yes | `{"magnitude": 0.2, "score": 0.2}` |
| `L8.shock.supply_break` | `event_llm_from_runtime_news` | `risk_discount` | 0.2 | yes | `{"magnitude": 0.2, "score": 0.2}` |
| `L6.mult.dcf` | `manual_design_review` | `valuation_rerating` | 0.15 | yes | `{"assumptions": {"discount_rate": "review_required", "forecast_horizon_years": 5, "terminal_growth": "review_required"}, "scalar": 0.15, "sensitivity": {"base": 0.15, "high": 0.3, "low": -0.05}}` |
| `L6.priced.realization_risk` | `manual_design_review` | `priced_in_discount` | 0.2 | yes | `{"drivers": ["run_up", "news_age", "priced_in"], "magnitude": 0.2}` |
| `L7.reflex.tag` | `manual_design_review` | `reflexivity_multiplier` | 0.050000000000000044 | yes | `{"multiplier": 1.05, "tag": "positive_feedback"}` |
| `L8.val.slope_risk_off` | `manual_design_review` | `risk_discount` | 0.18 | yes | `{"drivers": ["second_derivative", "risk_appetite", "overvalued"], "magnitude": 0.18}` |

## Interpretation

- This validates the bridge contract only. It does not prove the candidate value is correct.
- A row passing this dry-run can be numerically converted by the current production bridge if a reviewed candidate writes the same payload shape as Known/Proxy.
- `safe_to_upsert_without_review` remains governed by the candidate-evidence audit and is still 0.
