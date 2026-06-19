# A-share Unknown event evidence adjudication

- Generated: `2026-06-19T15:22:46+08:00`
- Event Unknown rows adjudicated: `2`
- Candidate examples reviewed: `14`
- Accepted candidates: `0`
- Rejected or ambiguous candidates: `14`
- Remaining Unknown rows: `2`
- Known-draft sufficient rows: `0`
- Auto Known-ready rows: `0`
- Approval-ready rows: `0`
- Contracts valid: `2`
- Contracts invalid: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | retained | accepted | rejected/ambiguous | status | production write |
|---|---:|---:|---:|---|---:|
| `L0.compete.new_entrant` | 6 | 0 | 6 | `no_clean_known_candidate_after_adjudication` | no |
| `L0.tech.substitute_tech` | 8 | 0 | 8 | `no_clean_known_candidate_after_adjudication` | no |

## Interpretation

- This adjudicates retained local candidates only; it does not create Known values.
- Accepted candidates would still require reviewer classification, bounded value generation, and approval.
- With zero accepted candidates, both rows remain Unknown and require stronger primary/source evidence.
