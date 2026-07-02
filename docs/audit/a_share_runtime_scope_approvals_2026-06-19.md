# A-share runtime scope approvals

- Generated: `2026-06-19T18:56:18+08:00`
- Target-scope rows checked: `2`
- Scope approval records: `2`
- Approved runtime target scopes: `2`
- Scope policy rejected: `0`
- Candidate runtime rows that would write if later approved: `3282`
- Runtime writes attempted: `0`
- Production writes allowed: `0`
- Score mutation: `scope approval records only; no realtime_current or production score mutation`

## Approved Scope Records

| dp_id | approval_id | target count | scope hash |
|---|---|---:|---|
| `L7.trade.gamma` | `codex-runtime-scope-20260619-l7-trade-gamma` | 1641 | `62ac8c6a673e` |
| `L9.media.short_report` | `codex-runtime-scope-20260619-l9-media-short-report` | 1641 | `e0dcd206b6dd` |

## Interpretation

- These records approve only the deterministic target-universe expansion contract.
- They do not create a controlled UPSERT batch and do not write runtime rows.
