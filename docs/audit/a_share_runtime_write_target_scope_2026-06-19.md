# A-share runtime write target-scope audit

- Generated: `2026-06-19T18:56:18+08:00`
- Approved write-plan entries: `2`
- Runtime A-share ts_codes: `1641`
- Config A-share ts_codes: `1641`
- Runtime/config A-share exact match: `True`
- Target-scope candidates: `2`
- Target-scope review required: `0`
- Target-scope approved: `2`
- Controlled batch plans required: `2`
- Candidate runtime rows that would write if approved: `3282`
- Upsert-ready entries: `0`
- Runtime writes attempted: `0`
- Production writes allowed: `0`
- Score mutation: `none; target-scope audit is read-only and does not alter realtime_current`

## Rows

| dp_id | scope status | target count | contract valid | candidate rows | blockers |
|---|---|---:|---:|---:|---|
| `L7.trade.gamma` | `scope_approved_batch_plan_required` | 1641 | yes | 1641 | controlled_batch_upsert_plan_required |
| `L9.media.short_report` | `scope_approved_batch_plan_required` | 1641 | yes | 1641 | controlled_batch_upsert_plan_required |

## Interpretation

- Current runtime and configured A-share universes match exactly for target-scope derivation.
- The derived scope is still a review-required candidate, not an executable UPSERT instruction.
- This audit creates no runtime rows and no production writes.
