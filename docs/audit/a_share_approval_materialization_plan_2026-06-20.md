# A-share approval materialization plan

- Generated: `2026-06-20T02:15:08+08:00`
- Approval packets checked: `25`
- A-share universe count: `1641`
- Fundamental packets: `19`
- Direct structured formula packets: `7`
- Direct structured formula plans ready for review: `7`
- Direct structured formula target range: `868` to `1639`
- Grain-join policy required: `0`
- Text full-match export required: `0`
- Market/event scope policy required: `14`
- Unsupported materialization policy: `0`
- Runtime materialization plans ready: `11`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; materialization planning audit is read-only and does not alter realtime_current`

## Class Counts

| Class | Count |
|---|---:|
| `direct_structured_per_stock_formula` | 7 |
| `market_or_event_scope_policy_required` | 14 |
| `structured_formula_grain_join_per_stock` | 1 |
| `text_evidence_subset_per_stock` | 3 |

## Rows

| dp_id | class | next step | target count | score range / sample scope |
|---|---|---|---:|---|
| `L0.compete.price_war` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L0.compete.share_concentration` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L0.cost.cac` | `direct_structured_per_stock_formula` | `approve_formula_materialization_plan` | 1639 | -1.0..0.594241 |
| `L0.cost.labor` | `direct_structured_per_stock_formula` | `approve_formula_materialization_plan` | 1289 | -1.0..1.0 |
| `L0.demand.terminal` | `direct_structured_per_stock_formula` | `approve_formula_materialization_plan` | 1607 | -0.990625..1.0 |
| `L0.demand.user_count` | `text_evidence_subset_per_stock` | `approve_text_evidence_subset_materialization_plan` | 4 | - |
| `L0.policy.access_license` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L0.policy.regulation` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L0.policy.subsidy` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L0.policy.tax_trade` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L0.price.contract_spot` | `structured_formula_grain_join_per_stock` | `approve_grain_join_materialization_plan` | 1005 | - |
| `L0.price.discount` | `text_evidence_subset_per_stock` | `approve_text_evidence_subset_materialization_plan` | 1 | - |
| `L0.price.pricing_power` | `direct_structured_per_stock_formula` | `approve_formula_materialization_plan` | 1546 | -1.0..1.0 |
| `L0.supply.capacity` | `direct_structured_per_stock_formula` | `approve_formula_materialization_plan` | 868 | -0.519216..1.0 |
| `L0.supply.chain_eff` | `direct_structured_per_stock_formula` | `approve_formula_materialization_plan` | 1517 | -1.0..1.0 |
| `L0.supply.channel_service` | `text_evidence_subset_per_stock` | `approve_text_evidence_subset_materialization_plan` | 1 | - |
| `L0.supply.inventory` | `direct_structured_per_stock_formula` | `approve_formula_materialization_plan` | 1529 | -1.0..0.5 |
| `L0.tech.ai_automation` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L0.tech.breakthrough` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L6.priced.realization_risk` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L7.reflex.tag` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L8.shock.black_swan` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L8.shock.supply_break` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L8.val.slope_risk_off` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |
| `L6.mult.dcf` | `market_or_event_scope_policy_required` | `approve_market_or_event_target_scope_policy` | 0 | - |

## Interpretation

- Direct structured formula rows have enough runtime inputs to package a reviewable per-stock materialization plan.
- Grain-join and text rows still need explicit target extraction policy before a write plan.
- Market/event rows should not be expanded to every A-share ticker without a reviewed target-scope policy.
- This report does not approve or execute runtime writes.
