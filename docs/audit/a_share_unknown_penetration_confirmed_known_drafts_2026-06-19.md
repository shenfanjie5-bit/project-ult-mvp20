# A-share Unknown penetration confirmed Known drafts

- Generated: `2026-06-19T20:46:53+08:00`
- Confirmation-gate rows: `1`
- Confirmed value-policy candidates: `0`
- Known draft rows: `1`
- Known drafts emitted: `0`
- Known drafts blocked: `1`
- Known draft contracts valid: `0`
- Ready for review staging: `0`
- Approval-ready rows: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; Known draft audit only and no realtime_current mutation`

## Statuses

| status | count |
|---|---:|
| `blocked_confirmation_missing` | 1 |

## Rows

| dp_id | status | ready for staging | errors |
|---|---|---:|---|
| `L0.demand.penetration` | `blocked_confirmation_missing` | no | missing confirmation record |

## Interpretation

- This report only emits Known drafts when the confirmation gate has a confirmed value policy.
- Emitted drafts are still review-only and require later staging/approval before runtime writes.
- The current report writes no runtime data and changes no scores.
