# A-share formula materialization batch execution

- Generated: `2026-06-20T02:17:29+08:00`
- Execution status: `dry_run_ready`
- Approved batch plans: `11`
- Preflight ready: `11`
- Preflight blocked: `0`
- Runtime rows would write: `11006`
- Runtime backups created: `0`
- Backup path: `None`
- Backup quick_check: `None`
- Runtime writes attempted: `0`
- Runtime rows written: `0`
- Post-write verified rows: `0`
- Post-write verification errors: `0`
- Production writes allowed: `0`
- Score mutation: `none; execution preflight is read-only and does not alter realtime_current`

## Rows

| dp_id | status | planned rows | inserts | updates | backup rows | would write | written | blockers |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `L0.cost.cac` | `dry_run_ready` | 1639 | 0 | 0 | 1639 | 1639 | 0 | none |
| `L0.cost.labor` | `dry_run_ready` | 1289 | 0 | 0 | 1289 | 1289 | 0 | none |
| `L0.demand.terminal` | `dry_run_ready` | 1607 | 0 | 0 | 1607 | 1607 | 0 | none |
| `L0.demand.user_count` | `dry_run_ready` | 4 | 4 | 0 | 0 | 4 | 0 | none |
| `L0.price.contract_spot` | `dry_run_ready` | 1005 | 1005 | 0 | 0 | 1005 | 0 | none |
| `L0.price.discount` | `dry_run_ready` | 1 | 1 | 0 | 0 | 1 | 0 | none |
| `L0.price.pricing_power` | `dry_run_ready` | 1546 | 0 | 0 | 1546 | 1546 | 0 | none |
| `L0.supply.capacity` | `dry_run_ready` | 868 | 0 | 0 | 868 | 868 | 0 | none |
| `L0.supply.chain_eff` | `dry_run_ready` | 1517 | 0 | 0 | 1517 | 1517 | 0 | none |
| `L0.supply.channel_service` | `dry_run_ready` | 1 | 1 | 0 | 0 | 1 | 0 | none |
| `L0.supply.inventory` | `dry_run_ready` | 1529 | 0 | 0 | 1529 | 1529 | 0 | none |

## Interpretation

- `dry_run_ready` means approved formula plans still match the current runtime DB.
- `dry_run_ready` does not create a backup and does not execute UPSERTs.
- `executed` means a SQLite backup was created before the bounded UPSERT.
