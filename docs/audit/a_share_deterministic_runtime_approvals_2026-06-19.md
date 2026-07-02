# A-share deterministic runtime approvals

- Generated: `2026-06-19T17:13:30+08:00`
- Manifest rows checked: `34`
- Approval records: `2`
- Approved deterministic runtime writes: `2`
- Deterministic policy rejected: `0`
- Non-deterministic rows left unapproved: `32`
- Production writes allowed: `0`
- Score mutation: `approval records only; no realtime_current or production score mutation`

## Approved Records

| dp_id | target | status | approval_id | payload hash |
|---|---|---|---|---|
| `L9.media.short_report` | `expectation_gap` | `Known` | `codex-deterministic-20260619-l9-media-short-report` | `b8982f2b839e` |
| `L7.trade.gamma` | `gamma_multiplier` | `NotApplicable` | `codex-deterministic-20260619-l7-trade-gamma` | `6af8c4ea8e39` |

## Interpretation

- Only deterministic neutral / NotApplicable staging payloads are approved here.
- Event-text, local-policy, manual-policy, and Unknown packets remain unapproved.
- Approval scope is `runtime_write`; production writes remain disabled.
