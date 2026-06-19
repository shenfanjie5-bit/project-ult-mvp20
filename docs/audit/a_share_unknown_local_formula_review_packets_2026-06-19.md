# A-share Unknown local formula review packets

- Generated: `2026-06-19T22:47:14+08:00`
- Local formula review packets: `2`
- Rows with candidate numerator: `2`
- Rows with direct denominator: `0`
- Rows with denominator candidates: `1`
- Rows with candidate formula shape: `1`
- Rows with formula-policy draft candidates: `1`
- Formula-policy review templates: `1`
- Formula-policy review template contracts valid: `1`
- Formula-policy review templates blank pending: `1`
- Rows with price-index context candidates: `1`
- Rows with candidate price-context shape: `1`
- Price-context review templates: `1`
- Price-context review template contracts valid: `1`
- Price-context review templates blank pending: `1`
- Rows with quantity or price index: `0`
- Rows with formula policy: `0`
- Formula inputs ready: `0`
- Formula probes available: `0`
- Bridge-probe-ready packets: `0`
- Selected value JSONs: `0`
- Known-draft-sufficient packets: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | candidate numerator | denominator candidate | policy draft | policy template | price-index context | price template | missing before Known | formula probe | bridge ready | production write |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `L0.cost.rent` | yes | yes | yes | yes | no | no | denominator_review, formula_policy_review | no | no | no |
| `L0.price.product_asp` | yes | no | no | no | yes | yes | quantity_or_price_index, formula_policy | no | no | no |

## Interpretation

- Candidate numerators are not enough to produce a final-score value.
- A runtime revenue denominator candidate can narrow rent review, but it still needs denominator policy and formula policy before a score probe.
- Rent now has a review-only formula-policy draft candidate, but proxy semantics, denominator policy, and cap/floor are still unapproved.
- Product ASP has broad macro CPI/PPI price-index context, but it still needs quantity, shipment volume, product-level volume, or a governed product-to-index mapping before a score probe.
- All packets remain Unknown, review-required, and non-writable.
