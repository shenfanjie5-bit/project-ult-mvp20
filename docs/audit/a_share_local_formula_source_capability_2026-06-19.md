# A-share local formula source capability

- Generated: `2026-06-19T16:02:35+08:00`
- Rows: `2`
- Source capability checks: `8`
- Checks with source candidates: `6`
- Header available but sample-empty checks: `1`
- Candidate context/proxy checks: `3`
- Review-policy-required checks: `3`
- External/text-required checks: `1`
- Formula blockers resolved by current sources: `0`
- Formula inputs ready after source scan: `0`
- Formula probes available: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | candidates | blockers resolved | formula ready | key conclusion |
|---|---:|---:|---:|---|
| `L0.cost.rent` | 3 | 0 | no | The cashflow header includes fa_fnc_leases, but the sampled semantic profile has zero non-empty rows. |
| `L0.price.product_asp` | 3 | 0 | no | The current structured inventory has business-segment revenue and macro PPI context, but no company product quantity, shipment volume, or governed product-level price index ready for ASP. |

## Interpretation

- Existing structured data can provide rent and ASP context, but it does not close the formula blockers.
- Rent needs either non-empty direct lease payment coverage or reviewed right-of-use proxy policy plus denominator.
- Product ASP needs company product quantity/shipment volume or a governed product/industry price index.
- Stock/futures trading volume fields are rejected as product quantity false positives.
