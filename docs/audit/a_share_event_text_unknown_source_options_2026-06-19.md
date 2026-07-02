# A-share event-text Unknown source options

- Generated: `2026-06-19T11:43:55+08:00`
- Unknown event-text rows: `2`
- Classification inputs ready: `2`
- Body text available: `2`
- Target-event evidence present: `0`
- Direct A-share transmission present: `0`
- Broad-market-only transmission: `2`
- Classifier-ready for review: `0`
- Target-event evidence still required: `2`
- Direct A-share transmission still required: `0`
- Auto Known candidates allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Resolution Status Counts

| Status | Count |
|---|---:|
| `requires_target_event_evidence` | 2 |

## Rows

| dp_id | class input | body text | target event | direct transmission | status | production write |
|---|---:|---:|---:|---:|---|---:|
| `L0.compete.new_entrant` | yes | yes | no | no | `requires_target_event_evidence` | no |
| `L0.tech.substitute_tech` | yes | yes | no | no | `requires_target_event_evidence` | no |

## Interpretation

- Current event-text data is fetchable and usable as bounded review input, but it is not sufficient for automatic Known values.
- Nine rows still lack target-event evidence in the fetched body text.
- Three rows have target-event evidence but still lack direct A-share transmission; broad China A50/futures hits are not enough.
- Production score-affecting writes remain disabled.
