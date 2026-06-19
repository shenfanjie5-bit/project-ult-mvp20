# A-share local single-dependency policy drafts

- Generated: `2026-06-19T07:32:35+08:00`
- Single-dependency tasks: `3`
- Draft Known review packets: `2`
- Draft Unknown packets: `1`
- Draft contracts valid: `3`
- Known drafts bridge-validated: `2`
- Safe to upsert without review: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Draft Status Counts

| Status | Count |
|---|---:|
| `draft_known_review_required` | 2 |
| `unknown_policy_required` | 1 |

## Rows

| dp_id | target | draft status | data status | contract | bridge | confidence | value |
|---|---|---|---|---:|---:|---:|---|
| `L0.demand.replacement` | `fundamental_score` | `unknown_policy_required` | `Unknown` | yes | - | 0.0 | `{"blocked_reason": "revenue_only_cannot_identify_replacement_cycle", "required_policy": "replacement demand needs product lifecycle, installed base, or cycle evidence beyond revenue scalar", "review_required": true}` |
| `L0.price.pricing_power` | `fundamental_score` | `draft_known_review_required` | `Known` | yes | yes | 0.42 | `{"components": {"neutral_gross_margin": 0.2, "sample_avg_gross_margin": 0.176963, "scale": 0.3}, "drivers": ["L5.is.gross_margin"], "score": -0.076791}` |
| `L0.supply.inventory` | `fundamental_score` | `draft_known_review_required` | `Known` | yes | yes | 0.42 | `{"components": {"neutral_inventory_to_assets": 0.2, "sample_avg_inventory_to_assets": 0.142331, "scale": 0.4}, "drivers": ["L5.bs.inventory"], "score": 0.144172}` |

## Interpretation

- This pilot produces review-only policy drafts for single-dependency local candidates when monotonic direction is defensible.
- `L0.demand.replacement` remains Unknown because revenue alone cannot identify replacement-cycle demand.
- Production score-affecting writes remain disabled.
