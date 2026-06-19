# A-share event Unknown primary-source confirmation

- Generated: `2026-06-19T18:06:05+08:00`
- Packets requiring confirmation: `2`
- Market HTML files scanned: `14956`
- Read errors: `0`
- Local candidates: `12`
- Local high-quality confirmation candidates: `0`
- Local supporting-context-only candidates: `12`
- Rows with local confirmation candidates: `0`
- Rows with supporting context only: `2`
- Rows without local confirmation candidates: `0`
- Classifier-ready rows: `0`
- Known-draft sufficient rows: `0`
- Approval-ready rows: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| packet | dp_id | status | local candidates | confirmation candidates | supporting only | contract | production write |
|---|---|---|---:|---:|---:|---:|---:|
| `L0.compete.new_entrant#strict_review_candidate#1` | `L0.compete.new_entrant` | `local_supporting_context_only` | 7 | 0 | 7 | yes | no |
| `L0.tech.substitute_tech#strict_review_candidate#7` | `L0.tech.substitute_tech` | `local_supporting_context_only` | 5 | 0 | 5 | yes | no |

## Interpretation

- Local high-quality confirmation candidates are still review inputs, not Known values.
- Supporting-context-only candidates are insufficient for score conversion.
- Rows without confirmation candidates still require external or primary-source acquisition.
- This audit creates no runtime writes and does not mutate final scores.
