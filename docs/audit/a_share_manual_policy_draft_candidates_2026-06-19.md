# A-share manual-policy draft candidates

- Generated: `2026-06-19T11:19:10+08:00`
- Manual-policy tasks: `4`
- Draft Known review packets: `4`
- Draft Unknown packets: `0`
- Draft contracts valid: `4`
- Draft contracts invalid: `0`
- Known drafts bridge-validated: `4`
- Review required: `4`
- Safe to upsert without review: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Draft Status Counts

| Status | Count |
|---|---:|
| `draft_known_review_required` | 3 |
| `draft_known_standard_dcf_assumption_review_required` | 1 |

## Rows

| dp_id | target | draft status | data status | contract | bridge | confidence | value |
|---|---|---|---|---:|---:|---:|---|
| `L6.mult.dcf` | `valuation_rerating` | `draft_known_standard_dcf_assumption_review_required` | `Known` | yes | yes | 0.32 | `{"components": {"cashflow_multiplier": 0.76, "fcf_yield_proxy": 0.020483, "growth_margin_multiplier": 0.8125, "negative_fcf_penalty": 0.2, "positive_fcf_sample_ratio": 0.333333, "quality_multiplier": 0.78625, "rates_multiplier": 1.0, "sample_avg_mcap_fcf": 48.820012, "sample_avg_revenue_growth_pct": 7.269742, "valuation_edge": -0.056342}, "dcf_assumptions": {"discount_rate": 0.095, "forecast_horizon_years": 5, "normalized_fcf_basis": "mixed_or_negative_fcf_penalized", "terminal_growth": 0.018174}, "drivers": ["L5.cf.fcf", "L5.is.revenue_growth", "L6.sens.rates", "L6.sens.growth_margin", "L6.sens.cashflow", "L6.mult.mcap_fcf"], "magnitude": 0.677314, "score": -0.677314}` |
| `L6.priced.realization_risk` | `priced_in_discount` | `draft_known_review_required` | `Known` | yes | yes | 0.45 | `{"components": {"news_age_component": 0.519667, "preprice_known_ratio": 0.087699, "priced_in_component": 0.05, "run_up_component": 0.137274}, "drivers": ["L6.priced.run_up", "L6.priced.news_age", "L5.surprise.preprice", "L8.val.priced_in"], "magnitude": 0.250584}` |
| `L7.reflex.tag` | `reflexivity_multiplier` | `draft_known_review_required` | `Known` | yes | yes | 0.4 | `{"components": {"active_inflow_component": 0.233993, "fomo_component": 0.2, "media_known_ratio": 0.048141, "reflex_score": 0.176573, "run_up_component": 0.137274}, "multiplier": 1.008829, "tag": "neutral"}` |
| `L8.val.slope_risk_off` | `risk_discount` | `draft_known_review_required` | `Known` | yes | yes | 0.45 | `{"components": {"expansion_known_ratio": 0.083144, "overvalued_component": 0.506922, "rates_component": 0.01, "risk_appetite_component": 0.0, "slope_component": 0.246004}, "drivers": ["L6.path.second_derivative", "L8.val.overvalued", "L7.env.risk_appetite", "L9.macro.rates", "L6.state.expansion_compression"], "magnitude": 0.235192}` |

## Interpretation

- This pilot generates review-only candidate values for manual-policy tasks that can be bounded from existing dependency evidence.
- `L6.mult.dcf` now emits an explicit standard-assumption DCF draft; it remains review-only until approved.
- Known drafts validate only payload shape and bridge reachability; they are not approved production inputs.
- Production score-affecting writes remain disabled.
