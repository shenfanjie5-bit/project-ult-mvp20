# A-share local structured source review packets

- Generated: `2026-06-19T12:42:16+08:00`
- Source-review packets: `4`
- Review candidate ready: `1`
- Supporting candidate needs quantity source: `1`
- External source required: `2`
- Direct Known-ready: `0`
- Formula inputs ready: `0`
- Candidate packets: `2`
- Candidate columns: `5`
- Empty candidate columns: `1`
- Excluded false positives: `407`
- Packet contracts valid: `4`
- Packet contracts invalid: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | status | candidates | missing formula inputs | contract | production write |
|---|---|---:|---:|---:|---:|
| `L0.cost.rent` | `review_candidate_ready` | 1 | 3 | yes | no |
| `L0.demand.frequency` | `external_source_required` | 0 | 3 | yes | no |
| `L0.demand.penetration` | `external_source_required` | 0 | 3 | yes | no |
| `L0.price.product_asp` | `supporting_candidate_needs_quantity_source` | 4 | 3 | yes | no |

## Interpretation

- `L0.cost.rent` has a reviewable lease-burden proxy candidate, but formula inputs are not complete.
- `L0.price.product_asp` has product-mix and revenue/cost support, but still needs unit volume, shipment volume, or a governed price index.
- `L0.demand.frequency` and `L0.demand.penetration` require external business sources or text/web extraction.
- All packets remain Unknown, review-required, and non-writable.
