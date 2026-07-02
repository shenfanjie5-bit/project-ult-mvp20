# A-share Unknown external business metric acquisition

- Generated: `2026-06-19T22:25:40+08:00`
- External business metric tasks: `3`
- Runtime dependency-ready tasks: `3`
- Runtime overlay hints: `7`
- Business metric groups: `12`
- Business metric groups ready: `0`
- Rows with supporting runtime context: `3`
- Rows with overlay business context candidates: `2`
- Overlay A-share files checked: `1646`
- Overlay business context Known nodes: `527`
- Overlay frequency context Known nodes: `166`
- Overlay penetration context Known nodes: `361`
- Overlay frequency direct Known/Unknown nodes: `0`/`1646`
- Overlay penetration direct Known/Unknown nodes: `0`/`1646`
- Rows with direct business metric source: `0`
- Rows requiring external/text source: `3`
- Excluded false positives: `238`
- Metric inputs ready: `0`
- Ready for Known draft: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | status | groups ready | runtime context | overlay context | false positives | production write |
|---|---|---:|---:|---:|---:|---:|
| `L0.demand.frequency` | `cadence_source_required` | 0/4 | yes | yes | 96 | no |
| `L0.demand.penetration` | `market_denominator_required` | 0/4 | yes | yes | 142 | no |
| `L0.demand.replacement` | `lifecycle_replacement_cycle_required` | 0/4 | yes | no | 0 | no |

## Interpretation

- Frequency and penetration have revenue context and adjacent overlay business context, but no direct reviewed cadence, denominator, or source-policy evidence.
- Replacement has revenue context and overlay hints, but no direct lifecycle or replacement-cycle source.
- These acquisition rows remain Unknown and cannot write to runtime scoring.
