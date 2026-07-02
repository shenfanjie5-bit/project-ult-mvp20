# A-share approval materialization batch plan

- Generated: `2026-06-20T02:15:09+08:00`
- Batch plan set: `a-share-formula-batch-c06b6a2166ce`
- Direct formula plans: `11`
- Batch-plan entries: `11`
- Contract-valid batch plans: `11`
- Batch-plan review required: `11`
- Batch-plan approved: `0`
- Planned UPSERT rows: `11006`
- Rows to insert: `1011`
- Rows to update: `0`
- Existing rows requiring backup: `9995`
- Runtime writes attempted: `0`
- Production writes allowed: `0`
- Score mutation: `none; formula materialization batch-plan audit is read-only and does not alter realtime_current`

## Rows

| dp_id | status | planned rows | inserts | updates | backup rows | plan hash | blockers |
|---|---|---:|---:|---:|---:|---|---|
| `L0.cost.cac` | `review_required` | 1639 | 0 | 0 | 1639 | `950f28ec9ed1` | controlled_batch_plan_requires_review_approval |
| `L0.cost.labor` | `review_required` | 1289 | 0 | 0 | 1289 | `ba3d961eb2dc` | controlled_batch_plan_requires_review_approval |
| `L0.demand.terminal` | `review_required` | 1607 | 0 | 0 | 1607 | `3e5b78267e0e` | controlled_batch_plan_requires_review_approval |
| `L0.demand.user_count` | `review_required` | 4 | 4 | 0 | 0 | `9c0e6de8f2c4` | controlled_batch_plan_requires_review_approval |
| `L0.price.contract_spot` | `review_required` | 1005 | 1005 | 0 | 0 | `2c2b6f07ef78` | controlled_batch_plan_requires_review_approval |
| `L0.price.discount` | `review_required` | 1 | 1 | 0 | 0 | `2fbccd471662` | controlled_batch_plan_requires_review_approval |
| `L0.price.pricing_power` | `review_required` | 1546 | 0 | 0 | 1546 | `44cc3d3f3111` | controlled_batch_plan_requires_review_approval |
| `L0.supply.capacity` | `review_required` | 868 | 0 | 0 | 868 | `0b56ac450eeb` | controlled_batch_plan_requires_review_approval |
| `L0.supply.chain_eff` | `review_required` | 1517 | 0 | 0 | 1517 | `7cdd48af6652` | controlled_batch_plan_requires_review_approval |
| `L0.supply.channel_service` | `review_required` | 1 | 1 | 0 | 0 | `f762463aa249` | controlled_batch_plan_requires_review_approval |
| `L0.supply.inventory` | `review_required` | 1529 | 0 | 0 | 1529 | `105dd9dc2cdb` | controlled_batch_plan_requires_review_approval |

## Interpretation

- This packages formula materialization into review-required controlled batch plans.
- The row-set hash binds the computed per-stock values from the current runtime inputs.
- This audit creates no approval records, performs no UPSERTs, and allows no production writes.
