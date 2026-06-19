# A-share formula materialization batch execution preflight

- Generated: `2026-06-20T01:08:55+08:00`
- Execution status: `dry_run_ready`
- Approved batch plans: `7`
- Preflight ready: `7`
- Preflight blocked: `0`
- Runtime rows would write: `9995`
- Runtime backups created: `0`
- Runtime writes attempted: `0`
- Production writes allowed: `0`
- Score mutation: `none; execution preflight is read-only and does not alter realtime_current`

## Rows

| dp_id | status | planned rows | inserts | updates | backup rows | would write | blockers |
|---|---|---:|---:|---:|---:|---:|---|
| `L0.cost.cac` | `dry_run_ready` | 1639 | 1639 | 0 | 0 | 1639 | none |
| `L0.cost.labor` | `dry_run_ready` | 1289 | 1289 | 0 | 0 | 1289 | none |
| `L0.demand.terminal` | `dry_run_ready` | 1607 | 1607 | 0 | 0 | 1607 | none |
| `L0.price.pricing_power` | `dry_run_ready` | 1546 | 1546 | 0 | 0 | 1546 | none |
| `L0.supply.capacity` | `dry_run_ready` | 868 | 868 | 0 | 0 | 868 | none |
| `L0.supply.chain_eff` | `dry_run_ready` | 1517 | 1517 | 0 | 0 | 1517 | none |
| `L0.supply.inventory` | `dry_run_ready` | 1529 | 1529 | 0 | 0 | 1529 | none |

## Interpretation

- `dry_run_ready` means approved formula plans still match the current runtime DB.
- This preflight does not create a backup and does not execute UPSERTs.
- The next step is an explicit backup plus bounded runtime UPSERT execution.
