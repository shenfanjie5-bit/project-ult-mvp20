# A-share local structured policy drafts

- Generated: `2026-06-19T10:51:32+08:00`
- Local structured tasks: `10`
- Draft Known review packets: `6`
- Draft Unknown packets: `4`
- Draft contracts valid: `10`
- Draft contracts invalid: `0`
- Known drafts bridge-validated: `6`
- Safe to upsert without review: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Draft Status Counts

| Status | Count |
|---|---:|
| `draft_known_pass_through_review_required` | 1 |
| `draft_known_review_required` | 5 |
| `unknown_policy_required` | 4 |

## Rows

| dp_id | target | draft status | data status | contract | bridge | confidence | value |
|---|---|---|---|---:|---:|---:|---|
| `L0.cost.cac` | `fundamental_score` | `draft_known_review_required` | `Known` | yes | yes | 0.36 | `{"components": {"neutral_ratio": 0.18, "sample_avg_sga_rd_ratio_revenue": 0.173185, "scale": 0.3}, "drivers": ["L5.is.sga_rd", "L5.is.revenue"], "score": 0.022717}` |
| `L0.cost.labor` | `fundamental_score` | `draft_known_review_required` | `Known` | yes | yes | 0.38 | `{"components": {"neutral_labor_cost_pct": 20.0, "pct_scale": 40.0, "sample_avg_labor_cost_pct": 17.994733, "sample_avg_labor_cost_yoy_pct": -0.920667, "yoy_scale": 30.0}, "drivers": ["L4.cost.labor", "L5.is.sga_rd"], "score": 0.080821}` |
| `L0.cost.rent` | `fundamental_score` | `unknown_policy_required` | `Unknown` | yes | - | 0.0 | `{"blocked_reason": "ppe_capex_cannot_identify_rent_or_lease_burden", "required_policy": "rent-cost drafts require lease/rent expense or reviewed asset-light policy, not only PPE/capex/goodwill proxies", "review_required": true}` |
| `L0.demand.frequency` | `fundamental_score` | `unknown_policy_required` | `Unknown` | yes | - | 0.0 | `{"blocked_reason": "revenue_growth_cannot_separate_purchase_frequency", "required_policy": "frequency needs transaction/order/usage cadence or reviewed decomposition beyond revenue growth", "review_required": true}` |
| `L0.demand.penetration` | `fundamental_score` | `unknown_policy_required` | `Unknown` | yes | - | 0.0 | `{"blocked_reason": "revenue_growth_cannot_identify_penetration_without_tam", "required_policy": "penetration needs TAM, market share, user-base, or installed-base evidence", "review_required": true}` |
| `L0.demand.terminal` | `fundamental_score` | `draft_known_review_required` | `Known` | yes | yes | 0.34 | `{"components": {"sample_avg_revenue_yoy_pct": 7.269742, "tanh_scale": 35.0}, "drivers": ["L5.is.revenue", "L5.is.revenue_growth"], "score": 0.204771}` |
| `L0.price.contract_spot` | `fundamental_score` | `draft_known_pass_through_review_required` | `Known` | yes | yes | 0.32 | `{"components": {"grain_join_policy": {"a_share_universe_count": 1641, "join_ready_a_share_count": 1007, "known_gross_margin_a_share_count": 1546, "missing_gross_margin_a_share_count": 95, "missing_raw_material_a_share_count": 539, "raw_material_industry_count": 7}, "gross_margin_buffer_component": -0.046075, "raw_material_relief_component": -0.017889, "sample_avg_gross_margin": 0.176963, "sample_avg_raw_material_pct_change": 0.053667}, "drivers": ["L0.cost.raw_material", "L5.is.gross_margin"], "score": -0.063964}` |
| `L0.price.product_asp` | `fundamental_score` | `unknown_policy_required` | `Unknown` | yes | - | 0.0 | `{"blocked_reason": "revenue_and_margin_cannot_identify_unit_asp_without_volume_mix", "required_policy": "ASP needs unit volume, product mix, or reviewed price-index evidence beyond revenue/gross margin", "review_required": true}` |
| `L0.supply.capacity` | `fundamental_score` | `draft_known_review_required` | `Known` | yes | yes | 0.34 | `{"components": {"neutral_capex_to_ppe": 0.02, "sample_avg_capex_to_ppe": 0.025049, "scale": 0.08}, "drivers": ["L5.cf.capex", "L5.bs.goodwill_ppe"], "score": 0.063117}` |
| `L0.supply.chain_eff` | `fundamental_score` | `draft_known_review_required` | `Known` | yes | yes | 0.38 | `{"components": {"neutral_ccc_days": 90.0, "sample_avg_ccc_days": 87.88, "scale": 180.0}, "drivers": ["L4.eff.turnover", "L4.eff.cycle"], "score": 0.011778}` |

## Interpretation

- This pilot emits review-only local structured drafts where a monotonic financial policy is defensible.
- Fields that require volume/mix/TAM/lease detail/text review remain Unknown.
- Contract/spot pricing is a review-only pass-through draft from raw-material futures, gross margin, and the explicit grain-join policy.
- Production score-affecting writes remain disabled.
