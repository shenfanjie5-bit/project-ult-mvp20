# A-share formula materialization batch approval gate

- Generated: `2026-06-20T00:59:38+08:00`
- Batch-plan rows checked: `7`
- Contract-valid batch plans: `7`
- Approval records seen: `7`
- Approval required: `7`
- Approval missing: `0`
- Approval rejected: `0`
- Approved formula batch plans: `7`
- Blank approval templates: `7`
- Planned UPSERT rows covered: `9995`
- Approved planned UPSERT rows: `9995`
- Runtime writes allowed: `7`
- Production writes allowed: `0`
- Score mutation: `none; approval gate is read-only and does not alter realtime_current`

## Rows

| dp_id | gate status | planned rows | plan hash | template valid |
|---|---|---:|---|---:|
| `L0.cost.cac` | `approved_controlled_formula_batch_plan` | 1639 | `950f28ec9ed1` | yes |
| `L0.cost.labor` | `approved_controlled_formula_batch_plan` | 1289 | `ba3d961eb2dc` | yes |
| `L0.demand.terminal` | `approved_controlled_formula_batch_plan` | 1607 | `3e5b78267e0e` | yes |
| `L0.price.pricing_power` | `approved_controlled_formula_batch_plan` | 1546 | `44cc3d3f3111` | yes |
| `L0.supply.capacity` | `approved_controlled_formula_batch_plan` | 868 | `0b56ac450eeb` | yes |
| `L0.supply.chain_eff` | `approved_controlled_formula_batch_plan` | 1517 | `7cdd48af6652` | yes |
| `L0.supply.inventory` | `approved_controlled_formula_batch_plan` | 1529 | `105dd9dc2cdb` | yes |

## Interpretation

- The batch plans are packaged, but approval records are still missing.
- Blank templates are hash-bound review inputs, not approvals.
- Runtime backup/execution remains blocked until valid approvals exist.
