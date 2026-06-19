# A-share approval target-scope readiness

- Generated: `2026-06-20T00:20:39+08:00`
- Approval packets checked: `25`
- Final-score-target ready packets: `25`
- Approval missing: `25`
- Source-sample reviewer packets complete: `25`
- Existing runtime target-scope policy dp_ids: `L7.trade.gamma, L9.media.short_report`
- Supported by existing target-scope policy: `0`
- Explicit target scopes present: `0`
- Target-scope ready after approval: `0`
- Target-scope policy required: `25`
- Per-stock value materialization required: `19`
- Market/event scope policy required: `6`
- Runtime materialization ready: `0`
- Approval-only not sufficient: `25`
- Production writes allowed: `0`
- Score mutation: `none; target-scope readiness audit is read-only and does not alter realtime_current`

## Scope Status Counts

| Scope status | Count |
|---|---:|
| `target_scope_policy_required` | 25 |

## Rows

| dp_id | target | source kind | risk class | scope status | next step | final-score ready | sample complete |
|---|---|---|---|---|---|---:|---:|
| `L0.compete.price_war` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.compete.share_concentration` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.cost.cac` | `fundamental_score` | `local_structured_policy_pilot` | `bulk_structured_review_candidate` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.cost.labor` | `fundamental_score` | `local_structured_policy_pilot` | `bulk_structured_review_candidate` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.demand.terminal` | `fundamental_score` | `local_structured_policy_pilot` | `individual_structured_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.demand.user_count` | `fundamental_score` | `local_structured_text_policy_pilot` | `individual_structured_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.policy.access_license` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.policy.regulation` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.policy.subsidy` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.policy.tax_trade` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.price.contract_spot` | `fundamental_score` | `local_structured_policy_pilot` | `individual_structured_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.price.discount` | `fundamental_score` | `local_structured_text_policy_pilot` | `individual_structured_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.price.pricing_power` | `fundamental_score` | `local_single_dependency_policy_pilot` | `bulk_structured_review_candidate` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.supply.capacity` | `fundamental_score` | `local_structured_policy_pilot` | `bulk_structured_review_candidate` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.supply.chain_eff` | `fundamental_score` | `local_structured_policy_pilot` | `bulk_structured_review_candidate` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.supply.channel_service` | `fundamental_score` | `local_structured_text_policy_pilot` | `borderline_structured_text_review_candidate` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.supply.inventory` | `fundamental_score` | `local_single_dependency_policy_pilot` | `bulk_structured_review_candidate` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.tech.ai_automation` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L0.tech.breakthrough` | `fundamental_score` | `event_text_policy_pilot` | `individual_event_evidence_review_required` | `target_scope_policy_required` | `per_stock_value_materialization_required` | yes | yes |
| `L6.priced.realization_risk` | `priced_in_discount` | `manual_policy_pilot` | `individual_policy_review_required` | `target_scope_policy_required` | `market_or_event_scope_policy_required` | yes | yes |
| `L7.reflex.tag` | `reflexivity_multiplier` | `manual_policy_pilot` | `individual_policy_review_required` | `target_scope_policy_required` | `market_or_event_scope_policy_required` | yes | yes |
| `L8.shock.black_swan` | `risk_discount` | `event_text_policy_pilot` | `individual_policy_review_required` | `target_scope_policy_required` | `market_or_event_scope_policy_required` | yes | yes |
| `L8.shock.supply_break` | `risk_discount` | `event_text_policy_pilot` | `individual_policy_review_required` | `target_scope_policy_required` | `market_or_event_scope_policy_required` | yes | yes |
| `L8.val.slope_risk_off` | `risk_discount` | `manual_policy_pilot` | `individual_policy_review_required` | `target_scope_policy_required` | `market_or_event_scope_policy_required` | yes | yes |
| `L6.mult.dcf` | `valuation_rerating` | `manual_policy_pilot` | `individual_policy_review_required` | `target_scope_policy_required` | `market_or_event_scope_policy_required` | yes | yes |

## Interpretation

- Approval records are necessary but not sufficient for these packets.
- Current runtime target-scope expansion is only defined for deterministic neutral/NotApplicable policies.
- Fundamental packets need per-stock materialization or an explicit target-scope policy before runtime writes.
- Non-fundamental policy/event packets need a reviewed market/event scope policy before runtime writes.
