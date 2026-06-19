# A-share formula materialization batch execution

- Generated: `2026-06-20T02:17:54+08:00`
- Execution status: `executed`
- Approved batch plans: `11`
- Preflight ready: `11`
- Preflight blocked: `0`
- Runtime rows would write: `11006`
- Runtime backups created: `1`
- Backup path: `runtime/backups/hot.sqlite.before_a-share-formula-batch-c06b6a2166ce_20260620T021744+0800.sqlite`
- Backup quick_check: `ok`
- Runtime writes attempted: `11`
- Runtime rows written: `11006`
- Post-write verified rows: `11006`
- Post-write verification errors: `0`
- Production writes allowed: `0`
- Score mutation: `runtime write executed; realtime_current was mutated with approved formula materialization rows`

## Rows

| dp_id | status | planned rows | inserts | updates | backup rows | would write | written | blockers |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `L0.cost.cac` | `executed` | 1639 | 0 | 0 | 1639 | 1639 | 1639 | none |
| `L0.cost.labor` | `executed` | 1289 | 0 | 0 | 1289 | 1289 | 1289 | none |
| `L0.demand.terminal` | `executed` | 1607 | 0 | 0 | 1607 | 1607 | 1607 | none |
| `L0.demand.user_count` | `executed` | 4 | 4 | 0 | 0 | 4 | 4 | none |
| `L0.price.contract_spot` | `executed` | 1005 | 1005 | 0 | 0 | 1005 | 1005 | none |
| `L0.price.discount` | `executed` | 1 | 1 | 0 | 0 | 1 | 1 | none |
| `L0.price.pricing_power` | `executed` | 1546 | 0 | 0 | 1546 | 1546 | 1546 | none |
| `L0.supply.capacity` | `executed` | 868 | 0 | 0 | 868 | 868 | 868 | none |
| `L0.supply.chain_eff` | `executed` | 1517 | 0 | 0 | 1517 | 1517 | 1517 | none |
| `L0.supply.channel_service` | `executed` | 1 | 1 | 0 | 0 | 1 | 1 | none |
| `L0.supply.inventory` | `executed` | 1529 | 0 | 0 | 1529 | 1529 | 1529 | none |

## Interpretation

- `dry_run_ready` means approved formula plans still match the current runtime DB.
- `dry_run_ready` does not create a backup and does not execute UPSERTs.
- `executed` means a SQLite backup was created before the bounded UPSERT.
