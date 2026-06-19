# A-share approval materialization batch plan

- Generated: `2026-06-20T00:37:00+08:00`
- Batch plan set: `a-share-formula-batch-faea2f8291a3`
- Direct formula plans: `7`
- Batch-plan entries: `7`
- Contract-valid batch plans: `7`
- Batch-plan review required: `7`
- Batch-plan approved: `0`
- Planned UPSERT rows: `9995`
- Rows to insert: `9995`
- Rows to update: `0`
- Existing rows requiring backup: `0`
- Runtime writes attempted: `0`
- Production writes allowed: `0`
- Score mutation: `none; formula materialization batch-plan audit is read-only and does not alter realtime_current`

## Rows

| dp_id | status | planned rows | inserts | updates | backup rows | plan hash | blockers |
|---|---|---:|---:|---:|---:|---|---|
| `L0.cost.cac` | `review_required` | 1639 | 1639 | 0 | 0 | `950f28ec9ed1` | controlled_batch_plan_requires_review_approval |
| `L0.cost.labor` | `review_required` | 1289 | 1289 | 0 | 0 | `ba3d961eb2dc` | controlled_batch_plan_requires_review_approval |
| `L0.demand.terminal` | `review_required` | 1607 | 1607 | 0 | 0 | `3e5b78267e0e` | controlled_batch_plan_requires_review_approval |
| `L0.price.pricing_power` | `review_required` | 1546 | 1546 | 0 | 0 | `44cc3d3f3111` | controlled_batch_plan_requires_review_approval |
| `L0.supply.capacity` | `review_required` | 868 | 868 | 0 | 0 | `0b56ac450eeb` | controlled_batch_plan_requires_review_approval |
| `L0.supply.chain_eff` | `review_required` | 1517 | 1517 | 0 | 0 | `7cdd48af6652` | controlled_batch_plan_requires_review_approval |
| `L0.supply.inventory` | `review_required` | 1529 | 1529 | 0 | 0 | `105dd9dc2cdb` | controlled_batch_plan_requires_review_approval |

## Interpretation

- This packages formula materialization into review-required controlled batch plans.
- The row-set hash binds the computed per-stock values from the current runtime inputs.
- This audit creates no approval records, performs no UPSERTs, and allows no production writes.
