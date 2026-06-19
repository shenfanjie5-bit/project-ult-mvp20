# A-share formula materialization Codex batch review

- Generated: `2026-06-20T00:59:38+08:00`
- Batch-plan rows checked: `7`
- Codex review approved: `7`
- Codex review rejected: `0`
- Approval records emitted: `7`
- Approved planned UPSERT rows: `9995`
- Runtime writes attempted: `0`
- Production writes allowed: `0`
- Score mutation: `approval records only; no realtime_current or production score mutation`

## Rows

| dp_id | review decision | planned rows | score min | score max | errors |
|---|---|---:|---:|---:|---|
| `L0.cost.cac` | `approved_controlled_formula_batch_plan` | 1639 | -1.0 | 0.594241 | none |
| `L0.cost.labor` | `approved_controlled_formula_batch_plan` | 1289 | -1.0 | 1.0 | none |
| `L0.demand.terminal` | `approved_controlled_formula_batch_plan` | 1607 | -0.990625 | 1.0 | none |
| `L0.price.pricing_power` | `approved_controlled_formula_batch_plan` | 1546 | -1.0 | 1.0 | none |
| `L0.supply.capacity` | `approved_controlled_formula_batch_plan` | 868 | -0.519216 | 1.0 | none |
| `L0.supply.chain_eff` | `approved_controlled_formula_batch_plan` | 1517 | -1.0 | 1.0 | none |
| `L0.supply.inventory` | `approved_controlled_formula_batch_plan` | 1529 | -1.0 | 0.5 | none |

## Interpretation

- Approval records authorize only the controlled formula batch-plan hashes.
- The review does not create a runtime backup and does not execute UPSERTs.
- Production writes remain disabled even after approval.
