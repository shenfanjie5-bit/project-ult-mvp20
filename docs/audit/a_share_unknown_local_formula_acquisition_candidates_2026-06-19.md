# A-share Unknown local formula acquisition candidates

- Generated: `2026-06-19T13:30:26+08:00`
- Local formula acquisition tasks: `2`
- Runtime dependency-ready tasks: `2`
- Sample CSV files checked: `6`
- Sample CSV files existing: `6`
- Sample CSV read errors: `0`
- Formula input groups: `8`
- Formula input groups ready: `0`
- Rows with candidate numerator: `2`
- Rows with direct denominator: `0`
- Rows with quantity or price index: `0`
- Rows with formula policy: `0`
- Formula inputs ready: `0`
- Ready for Known draft: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | status | candidate columns | input groups ready | formula ready | production write |
|---|---|---:|---:|---:|---:|
| `L0.cost.rent` | `proxy_available_denominator_policy_missing` | 1 | 0/4 | no | no |
| `L0.price.product_asp` | `revenue_mix_available_quantity_missing` | 4 | 0/4 | no | no |

## Interpretation

- Rent has a lease-proxy candidate, but lacks direct rent/lease payment, denominator, and reviewed proxy policy.
- Product ASP has product/mix and revenue context, but lacks quantity or governed price-index input.
- These packets are formula acquisition evidence only; no runtime score writes are allowed.
