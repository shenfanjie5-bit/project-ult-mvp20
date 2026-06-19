# A-share Unknown external business metric readiness queue

- Generated: `2026-06-19T14:03:28+08:00`
- Review packets: `99`
- P0 formula-policy-only candidates: `18`
- P1 period/unit required: `52`
- P2 denominator required: `29`
- Metric inputs ready: `0`
- Known-draft sufficient: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## dp_id Priority Split

| dp_id | packets | P0 | P1 | P2 | top next action |
|---|---:|---:|---:|---:|---|
| `L0.demand.frequency` | 4 | 1 | 2 | 1 | `P0_formula_policy_only` |
| `L0.demand.penetration` | 71 | 17 | 50 | 4 | `P0_formula_policy_only` |
| `L0.demand.replacement` | 24 | 0 | 0 | 24 | `P2_denominator_required` |

## Interpretation

- P0 packets are closest to a Known draft but still require reviewed bounds and formula policy.
- P1 packets need period or unit extraction before formula review.
- P2 packets need a denominator or normalizer before numeric conversion.
- Runtime and production writes remain disabled.
