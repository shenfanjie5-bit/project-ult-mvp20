# A-share formula materialization batch approval gate

- Generated: `2026-06-20T02:17:16+08:00`
- Batch-plan rows checked: `11`
- Contract-valid batch plans: `11`
- Approval records seen: `11`
- Approval required: `11`
- Approval missing: `0`
- Approval rejected: `0`
- Approved formula batch plans: `11`
- Blank approval templates: `11`
- Planned UPSERT rows covered: `11006`
- Approved planned UPSERT rows: `11006`
- Runtime writes allowed: `11`
- Production writes allowed: `0`
- Score mutation: `none; approval gate is read-only and does not alter realtime_current`

## Rows

| dp_id | gate status | planned rows | plan hash | template valid |
|---|---|---:|---|---:|
| `L0.cost.cac` | `approved_controlled_formula_batch_plan` | 1639 | `950f28ec9ed1` | yes |
| `L0.cost.labor` | `approved_controlled_formula_batch_plan` | 1289 | `ba3d961eb2dc` | yes |
| `L0.demand.terminal` | `approved_controlled_formula_batch_plan` | 1607 | `3e5b78267e0e` | yes |
| `L0.demand.user_count` | `approved_controlled_formula_batch_plan` | 4 | `9c0e6de8f2c4` | yes |
| `L0.price.contract_spot` | `approved_controlled_formula_batch_plan` | 1005 | `2c2b6f07ef78` | yes |
| `L0.price.discount` | `approved_controlled_formula_batch_plan` | 1 | `2fbccd471662` | yes |
| `L0.price.pricing_power` | `approved_controlled_formula_batch_plan` | 1546 | `44cc3d3f3111` | yes |
| `L0.supply.capacity` | `approved_controlled_formula_batch_plan` | 868 | `0b56ac450eeb` | yes |
| `L0.supply.chain_eff` | `approved_controlled_formula_batch_plan` | 1517 | `7cdd48af6652` | yes |
| `L0.supply.channel_service` | `approved_controlled_formula_batch_plan` | 1 | `f762463aa249` | yes |
| `L0.supply.inventory` | `approved_controlled_formula_batch_plan` | 1529 | `105dd9dc2cdb` | yes |

## Interpretation

- The batch plans are packaged, but approval records are still missing.
- Blank templates are hash-bound review inputs, not approvals.
- Runtime backup/execution remains blocked until valid approvals exist.
