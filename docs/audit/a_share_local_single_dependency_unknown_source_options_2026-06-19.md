# A-share local single-dependency Unknown source options

- Generated: `2026-06-19T22:55:56+08:00`
- Unknown local single-dependency rows: `1`
- Runtime dependencies ready: `1`
- Direct replacement-cycle source-ready rows: `0`
- Overlay/source hints: `1`
- Rows with overlay lifecycle context candidates: `1`
- Overlay lifecycle Known nodes: `205`
- Overlay replacement Known nodes: `0`
- Overlay replacement Unknown nodes: `1646`
- Lifecycle/replacement-cycle source required: `1`
- Reviewed policy required: `1`
- Lifecycle-policy review templates: `1`
- Lifecycle-policy review template contracts valid: `1`
- Lifecycle-policy review template contracts invalid: `0`
- Lifecycle-policy review templates blank pending: `1`
- Lifecycle-policy review template inputs ready: `0`
- Auto Known candidates allowed: `0`
- Known-draft sufficient rows: `0`
- Approval-ready rows: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Resolution Status Counts

| Status | Count |
|---|---:|
| `requires_lifecycle_or_replacement_cycle_source` | 1 |

## Rows

| dp_id | runtime deps | direct cycle source ready | overlay hints | lifecycle context | policy template | status | production write |
|---|---:|---:|---:|---:|---:|---|---:|
| `L0.demand.replacement` | yes | no | 7 | yes | yes | `requires_lifecycle_or_replacement_cycle_source` | no |

## Interpretation

- Revenue is a ready runtime dependency, but it is not replacement-cycle evidence.
- Local stock overlays contain lifecycle context that can guide review, but it is not direct replacement-cycle source evidence.
- The lifecycle-policy review template is a blank reviewer handoff; it is not classifier-ready, Known-ready, or production-write approval.
- `L0.demand.replacement` needs lifecycle, installed-base, renewal, shipment, user, or reviewed overlay evidence before a Known value is defensible.
- Existing industry graph or stock overlay hints can guide review, but they are not automatic production values.
- Production score-affecting writes remain disabled.
