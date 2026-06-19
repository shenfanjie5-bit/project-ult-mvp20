# A-share local structured Unknown source options

- Generated: `2026-06-19T10:51:52+08:00`
- Unknown local structured rows: `4`
- Runtime dependencies ready: `4`
- Direct structured source-ready rows: `0`
- Overlay/source hints: `4`
- New mapping or text extraction required: `4`
- Reviewed policy required: `0`
- Partial Known unlock candidates: `0`
- Auto Known candidates allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Resolution Status Counts

| Status | Count |
|---|---:|
| `requires_market_share_or_tam_source` | 1 |
| `requires_new_field_mapping_or_text_extraction` | 1 |
| `requires_volume_mix_or_price_index` | 1 |
| `requires_volume_or_usage_source` | 1 |

## Rows

| dp_id | runtime deps | direct source ready | overlay hints | status | partial unlock | production write |
|---|---:|---:|---:|---|---:|---:|
| `L0.cost.rent` | yes | no | 1 | `requires_new_field_mapping_or_text_extraction` | no | no |
| `L0.demand.frequency` | yes | no | 5 | `requires_volume_or_usage_source` | no | no |
| `L0.demand.penetration` | yes | no | 3 | `requires_market_share_or_tam_source` | no | no |
| `L0.price.product_asp` | yes | no | 5 | `requires_volume_mix_or_price_index` | no | no |

## Interpretation

- Current runtime dependencies are useful evidence packs, but none directly contains the target business field.
- Four rows need new mapped fields or text extraction before Known output is defensible.
- `L0.price.contract_spot` can move first after a reviewed grain-join/pass-through policy because the current candidate evidence already has a partial join-ready set.
- Production score-affecting writes remain disabled.
