# A-share score-field closure audit

- Generated: `2026-06-19T19:45:29+08:00`
- Score mutation: `none; audit is read-only`
- Spec total config/runtime: `256` / `256`
- Spec total matches runtime: `True`
- Score-relevant closed fields: `121` / `174`
- Blocking gaps: `32`
- Candidate-ready blockers: `32`
- Candidate-not-ready blockers: `0`
- Safe to upsert without review: `0`
- Direct structured Tushare remaining: `0`

## Closure Status Counts

| Status | Count |
|---|---:|
| `closed_reaches_final_score` | 121 |
| `no_valid_a_share_target_data` | 7 |
| `non_scoring_spec` | 82 |
| `overlay_only_no_score_candidate` | 28 |
| `valid_real_but_formula_unmapped` | 18 |

## Blocking Gaps

| dp_id | target | closure | candidate | route | dependencies | repair |
|---|---|---|---|---|---|---|
| `L0.compete.new_entrant` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.industry.compete_risk`, `L9.media.report` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.compete.price_war` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.industry.compete_risk`, `L9.media.report` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.compete.share_concentration` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.industry.compete_risk`, `L9.media.report` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.cost.cac` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.sga_rd`, `L5.is.revenue` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.cost.labor` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.sga_rd`, `L4.cost.labor` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.cost.rent` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.bs.goodwill_ppe`, `L5.cf.capex` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.demand.frequency` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.revenue`, `L5.is.revenue_growth` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.demand.penetration` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.revenue`, `L5.is.revenue_growth` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.demand.replacement` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.revenue` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.demand.terminal` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.revenue`, `L5.is.revenue_growth` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.demand.user_count` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.revenue`, `L9.disclosure.qa_recent` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.policy.access_license` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.industry.policy_change`, `L9.media.report` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.policy.regulation` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.industry.policy_change`, `L9.media.report` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.policy.subsidy` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.industry.policy_change`, `L9.media.report` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.policy.tax_trade` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.industry.policy_change`, `L9.macro.fx` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.price.contract_spot` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate_with_grain_join` | `local_llm_closed_loop` | `L0.cost.raw_material`, `L5.is.gross_margin` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.price.discount` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.gross_margin`, `L9.disclosure.qa_recent` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.price.pricing_power` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.gross_margin` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.price.product_asp` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.revenue`, `L5.is.gross_margin` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.supply.capacity` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.cf.capex`, `L5.bs.goodwill_ppe` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.supply.chain_eff` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L4.eff.turnover`, `L4.eff.cycle` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.supply.channel_service` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.is.sga_rd`, `L9.disclosure.qa_recent` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.supply.inventory` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_local_llm_candidate` | `local_llm_closed_loop` | `L5.bs.inventory` | `candidate_generation_required:local_llm_closed_loop` |
| `L0.tech.ai_automation` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.media.report`, `L9.industry.compete_risk` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.tech.breakthrough` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.media.report`, `L9.industry.compete_risk` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L0.tech.substitute_tech` | `fundamental_score` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.media.report`, `L9.industry.compete_risk` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L6.mult.dcf` | `valuation_rerating` | `no_valid_a_share_target_data` | `ready_for_manual_design_candidate` | `manual_design_review` | `L5.cf.fcf`, `L5.is.revenue_growth`, `L6.sens.rates`, `L6.sens.growth_margin`, `L6.sens.cashflow`, `L6.mult.mcap_fcf` | `candidate_generation_required:manual_design_review` |
| `L6.priced.realization_risk` | `priced_in_discount` | `no_valid_a_share_target_data` | `ready_for_manual_design_candidate` | `manual_design_review` | `L6.priced.run_up`, `L6.priced.news_age`, `L5.surprise.preprice`, `L8.val.priced_in` | `candidate_generation_required:manual_design_review` |
| `L7.reflex.tag` | `reflexivity_multiplier` | `no_valid_a_share_target_data` | `ready_for_manual_design_candidate` | `manual_design_review` | `L7.flow.active_inflow`, `L7.mood.fomo`, `L7.mood.media_social`, `L6.priced.run_up` | `candidate_generation_required:manual_design_review` |
| `L8.shock.black_swan` | `risk_discount` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.media.report`, `L9.macro.geo` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L8.shock.supply_break` | `risk_discount` | `overlay_only_no_score_candidate` | `ready_for_event_llm_candidate` | `event_llm_from_runtime_news` | `L9.media.report`, `L9.industry.compete_risk` | `candidate_generation_required:event_llm_from_runtime_news` |
| `L8.val.slope_risk_off` | `risk_discount` | `no_valid_a_share_target_data` | `ready_for_manual_design_candidate` | `manual_design_review` | `L6.path.second_derivative`, `L8.val.overvalued`, `L7.env.risk_appetite`, `L9.macro.rates`, `L6.state.expansion_compression` | `candidate_generation_required:manual_design_review` |

## Interpretation

- A field is counted as closed only when current evidence reaches the production score path: participating spec, Known/Proxy non-mock runtime or score-capable overlay, numeric conversion, and final score sink.
- Candidate-ready means dependency evidence exists; it is not treated as score completion because no reviewed target runtime row has been written.
- Existing Tushare/AKShare rows currently support candidate generation for 32 blockers, but direct structured Tushare gaps are already exhausted.
- The remaining work is target-value generation/review, then validating that regenerated rows move from `no_valid_a_share_target_data` to `closed_reaches_final_score` in this audit.
